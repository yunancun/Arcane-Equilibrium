# M3 健康監控 On-Call Response SOP

**狀態：** Draft（Sprint 1A-β deliverable；V106 schema + M3 ADR land 後 verify）
**版本：** v0.1（2026-05-21）
**Runbook ID：** RUNBOOK-M3-HEALTH-001
**Module：** M3 Self-Monitoring / Auto-Diagnostics / Health-Aware Degradation
**Severity coverage：** SEV-1 / SEV-2 / SEV-3（對應 4-state ladder）
**On-call role：** On-call PM + Operator（Cowork 提供 narrative summary，不做 state transition）
**Depends on：** v5.8 §2 M3 (line 123-151) / V106 schema (hypertable 7d chunk + 7d compression + 90d retention，pending CR-8) / ADR-0034 (LAL 1+2 在 HEALTH_DEGRADED 時 halt 對齊) / **ADR-0042 (M3 governance authority — single health authority + 4-state ladder + 6 domain + amplification/cascade cap；R4 NEW-H-3 reverse-ref patch 2026-05-21)** / AMD-2026-05-21-01 (M3 opt-in scope 行為)

> **Hands off — operator only**：HEALTH_CATASTROPHIC 觸發既有 5-gate kill；M3 auto-degradation 是 state machine 內部行為，**operator 不應手動編輯 V106 row 來「降速」health state**；必要時走 emergency disable IPC + 24h postmortem。

---

## 1. TL;DR / 用途

M3 把 v5.7 baseline 既有 healthcheck 從「**觀察**」升級為「**可動作**」。系統根據 6 個 health domain 的 probe 結果自動進入 4 個 state（HEALTH_NORMAL / WARN / DEGRADED / CRITICAL；HEALTH_CATASTROPHIC 走既有 kill criteria）。各 state 對應不同 degradation 行為（throttle Tier 1、halt 新單、drain position）。

本 runbook 規範 4 類事件：(a) **state 轉換時 on-call 響應**（4 state 各對應 SEV）/ (b) **6 health domain 各自 triage**（WS / REST / DB / Disk / Engine / Strategy）/ (c) **amplification loop cap 觸發處置**（防止 single anomaly = ∞ state change）/ (d) **HEALTH_DEGRADED → LAL Tier 自動降階驗收 SOP**（per §11.5 CR-15 5-gate inheritance）。

M3 **不**取代既有 `[59] h0_block_acceptance` / `[45] pricing_binding` / `engine_watchdog.py --status` 等 healthcheck；M3 是這些 probe 之上的 **state machine + 響應 layer**。

---

## 2. Detection / Alarm Symptoms

| Symptom | 來源 | 對應 section |
|---|---|---|
| Console 顯示 health state 由 NORMAL 跳 WARN / DEGRADED / CRITICAL | `learning.health_state_transitions` | §4 triage |
| Slack `#ops-warn` 收到 HEALTH_DEGRADED notification | M3 alert router | §4-5 |
| LAL 1 / LAL 2 auto-approve 突然全部 fall-back Advisory | `learning.lal_audit.gate_fail_reasons` 含 `health_degraded` | §7 LAL 降階驗收 |
| Engine metric 個別 domain 異常（WS latency p95 / DB write backlog / disk usage） | 個別 probe healthcheck | §6 6 domain triage |
| Strategy-level metric 異常（fill rate ↓ / slippage trend ↑ / lease grant rate ↓） | `learning.strategy_health_metrics` | §6 domain 6 |
| 同一 anomaly 24h 內觸發 state change ≥ 2 次 | amplification loop cap log | §8 loop cap |

---

## 3. Severity Matrix（對應 4-state ladder）

| State | Severity | Impact | Response time | Escalation path |
|---|---|---|---|---|
| **HEALTH_NORMAL** | n/a | 系統正常；無 degradation 行為 | n/a | 不通知 |
| **HEALTH_WARN** | SEV-3 | 觀察級；emit alert；無 behavior change；Slack `#ops-info` | < 4h | On-call PM 看 dashboard；無 escalate；登錄 12-week trend |
| **HEALTH_DEGRADED** | SEV-2 | Throttle 非關鍵策略：LAL 1 reparam halted、LAL 2 auto-approve fall-back Advisory；Stage 4 continues | < 30 min | On-call PM 加入 + 跑 §4 triage；4h 內判 RECOVER 或升 CRITICAL |
| **HEALTH_CRITICAL** | SEV-1 | 停新單、drain 既有 position per 既有 kill criteria；Slack `#ops-critical` | < 5 min | Operator + PM 立刻加入；30 min 內判 RECOVER 或升 CATASTROPHIC |
| **HEALTH_CATASTROPHIC** | SEV-1 | 既有 kill criteria 觸發（per CLAUDE.md §四 D2 portfolio cum loss > $3,000 等） | < 5 min | 既有 kill runbook（本 runbook scope 外） |

> **判定 state 升降**：M3 state machine 內部根據 6 domain 計分；on-call 不該手動編 V106 row 跳 state。必要時透過 IPC `patch_health_state_force` + 強制 audit row（emergency only，per §5）。

---

## 4. Initial Triage Checklist（5-10 步）

```bash
# Step 1 — 當前 health state + 6 domain score
curl -sS http://localhost:8001/api/v1/health/m3/state | jq
# expected:
#   .state ∈ {NORMAL, WARN, DEGRADED, CRITICAL, CATASTROPHIC}
#   .domains: {ws_latency, rest_success, db_backlog, disk_usage, engine_resource, strategy_metric}
#   .last_transition_at (ms ago) + .last_transition_reason
```

```bash
# Step 2 — 確認 state 不是 amplification loop cap 觸發的偽轉換
psql -h trade-core -U openclaw -d openclaw -c "
SELECT created_at, from_state, to_state, trigger_reason, amplification_cap_applied
FROM learning.health_state_transitions
WHERE created_at > NOW() - INTERVAL '24 hours'
ORDER BY id DESC LIMIT 30;"
# decision branch:
#   - amplification_cap_applied=true → §8 loop cap 處置
#   - 同 trigger_reason 24h 內 ≥ 2 row → §8 single anomaly 反復觸發
```

```bash
# Step 3 — engine_watchdog baseline 不能炸（M3 無法在 engine dead 時運作）
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py \
  --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --status"
# decision branch:
#   - engine_alive=false → 不屬本 runbook scope；轉 engine watchdog runbook
#   - snapshot age > 45s → engine 接近 stale；§6 engine_resource domain triage
```

```bash
# Step 4 — 確認 6 個 baseline healthcheck 與 M3 state 一致
psql -h trade-core -U openclaw -d openclaw -c "
SELECT check_name, status, message, created_at
FROM learning.passive_wait_audit
WHERE check_name IN ('h0_block_acceptance', 'pricing_binding', 'edge_estimator', 'live_auth_watcher')
  AND created_at > NOW() - INTERVAL '1 hour'
ORDER BY id DESC LIMIT 50;"
# decision branch:
#   - 多條 baseline check FAIL 但 M3 state = NORMAL → §8 M3 probe 漏接 baseline 信號（SEV-2）
```

```bash
# Step 5 — 確認 LAL gate 是否已自動降階（state ≥ DEGRADED 必降）
psql -h trade-core -U openclaw -d openclaw -c "
SELECT COUNT(*) FILTER (WHERE auto_approved = true) AS auto_count,
       COUNT(*) FILTER (WHERE auto_approved = false AND payload->>'gate_fail_reasons' LIKE '%health_degraded%') AS health_fallback_count
FROM learning.lal_audit
WHERE created_at > NOW() - INTERVAL '1 hour';"
# decision branch:
#   - state=DEGRADED 但 auto_count > 0 且 health_fallback_count = 0 → §7 LAL 降階驗收失敗（SEV-1）
```

```bash
# Step 6 — 確認 alert 路徑（Slack + email + Console banner）健康
curl -sS http://localhost:8001/api/v1/notify/health | jq '.slack_ok, .email_ok, .console_banner_ok'
# 任一 false → SEV-2 額外 finding；M3 alert 失效 = on-call 不知情風險
```

```bash
# Step 7 — Strategy-level 6th domain 詳細
curl -sS http://localhost:8001/api/v1/health/m3/strategy | jq
# expected per strategy: fill_rate_vs_intent, slippage_trend_30m, lease_grant_rate, decay_signal
# decision branch:
#   - 任一 strategy 異常但 state=NORMAL → §6 domain 6 triage
```

```bash
# Step 8 —（only if CRITICAL or amplification cap stuck）emergency unlatch
curl -sS -X POST -H "Cookie: $OPERATOR_SESSION_COOKIE" \
  -d '{"reason":"<rca_reason>", "expected_state":"WARN"}' \
  http://localhost:8001/api/v1/health/m3/force_state
# expected: 200 OK + audit row force_applied=true；§9 escalate；24h postmortem 必補
```

---

## 5. Mitigation — State Recovery 路徑

### 5.1 HEALTH_WARN → NORMAL

- 觀察 4h；如 domain score 自然回復 → 自動回 NORMAL
- 不需 operator click；登錄 12-week trend 即可

### 5.2 HEALTH_DEGRADED → WARN / NORMAL

- §4 triage 完成後識別 root cause
- 修復 root cause（如 DB backlog 排空 / WS reconnect 成功 / 個別策略 fill rate 回復）
- 等待 10 min 觀察期；M3 state machine 自動評估降階
- **不應**手動跳 NORMAL，必走 DEGRADED → WARN → NORMAL 路徑（per state machine invariant）

### 5.3 HEALTH_CRITICAL → DEGRADED

- 既有 kill criteria 已 drain；M3 等待 30 min 觀察 root cause
- Root cause 修復後 + 30 min stable → state machine 自動降到 DEGRADED
- Stage 4 策略 size 不自動回滿；走 Operator manual ramp（per AMD-2026-05-15-01）

### 5.4 Rollback option

如 state machine 行為本身 regression（如 NORMAL → CRITICAL 跳階；或不降階）：

```bash
# Emergency disable M3 auto-degradation（不停 probe，只停 state change action）
curl -sS -X POST -H "Cookie: $OPERATOR_SESSION_COOKIE" \
  -d '{"auto_degradation":false}' \
  http://localhost:8001/api/v1/health/m3/config
# 預期 effect：probe 持續寫 V106 row；state transition 寫 row 但 LAL halt / new order halt 等 downstream action 停
# 預期 rollback：root cause 修好後 → 重新 enable + 觀察 30 min
# 立刻 §9 escalate
```

---

## 6. 6 Health Domain 各自 Triage Checklist

### Domain 1 — Exchange WS Latency / Dropout

```bash
# WS p95 + dropout 24h
psql -h trade-core -U openclaw -d openclaw -c "
SELECT date_trunc('hour', created_at) AS hour,
       MAX(ws_latency_p95_ms) AS p95, MAX(dropout_count_1h) AS dropouts
FROM learning.health_observations
WHERE domain = 'ws_latency' AND created_at > NOW() - INTERVAL '24 hours'
GROUP BY 1 ORDER BY 1 DESC LIMIT 24;"
# decision branch:
#   p95 > 200ms / dropouts > 5/h → DEGRADED candidate
```

### Domain 2 — REST API Success / Retry

```bash
psql -h trade-core -U openclaw -d openclaw -c "
SELECT endpoint, COUNT(*) FILTER (WHERE retcode = 0) AS ok,
       COUNT(*) FILTER (WHERE retcode != 0) AS fail
FROM learning.bybit_rest_audit
WHERE created_at > NOW() - INTERVAL '1 hour' GROUP BY 1 ORDER BY 3 DESC LIMIT 20;"
# decision branch:
#   個別 endpoint fail rate > 5% → DEGRADED candidate
#   全 endpoint fail（如 IP ban） → CRITICAL
```

### Domain 3 — DB Write Backlog

```bash
psql -h trade-core -U openclaw -d openclaw -c "
SELECT pg_stat_user_tables.relname, n_dead_tup, last_autovacuum
FROM pg_stat_user_tables
WHERE schemaname IN ('trading', 'learning', 'market')
ORDER BY n_dead_tup DESC LIMIT 10;"
# decision branch:
#   n_dead_tup > 1M 且 last_autovacuum > 24h ago → vacuum 阻塞 → DEGRADED
```

### Domain 4 — Disk Usage（audit log growth）

```bash
ssh trade-core "df -h /var/lib/postgresql /tmp/openclaw"
# decision branch:
#   /var/lib/postgresql > 85% → DEGRADED + V106 retention 提早觸發
#   > 95% → CRITICAL（PG 可能拒寫）
```

### Domain 5 — Engine Memory / CPU

```bash
ssh trade-core "ps -o pid,vsz,rss,pcpu,etime,cmd -p \$(pgrep openclaw_engine)"
# decision branch:
#   rss > 8 GB（per 128GB constraint LLM ~54GB / PG 4-8GB）→ DEGRADED
#   pcpu > 80% sustained 5m → DEGRADED
```

### Domain 6 — Strategy-Level Metric

```bash
psql -h trade-core -U openclaw -d openclaw -c "
SELECT strategy_name,
       fill_rate_vs_intent_30m, slippage_trend_30m_bps, lease_grant_rate_30m
FROM learning.strategy_health_metrics
WHERE created_at > NOW() - INTERVAL '30 minutes'
ORDER BY strategy_name;"
# decision branch:
#   fill_rate_vs_intent < 50% sustained 30m → strategy DEGRADED
#   slippage_trend_30m_bps > 2σ historical → strategy DEGRADED
#   lease_grant_rate < 80% sustained 30m → governance gate stuck
```

---

## 7. HEALTH_DEGRADED → LAL Tier 自動降階驗收 SOP

**Invariant**（per v5.8 §11.5 / CR-15）：HEALTH_DEGRADED 觸發時 LAL 1 reparam halt + LAL 2 auto-approve fall-back Advisory。

### 驗收步驟

```bash
# Verify 1 — DEGRADED 後 60s 內 LAL 1+2 應全 fall-back
sleep 60
psql -h trade-core -U openclaw -d openclaw -c "
SELECT COUNT(*) FILTER (WHERE lal_level IN (1,2) AND auto_approved = true
                        AND created_at > NOW() - INTERVAL '60 seconds') AS leak_count
FROM learning.lal_audit;"
# expected: leak_count = 0；如 > 0 → §11.5 5-gate inheritance 違反（SEV-1）
```

```bash
# Verify 2 — gate_fail_reasons 應含 'health_degraded'
psql -h trade-core -U openclaw -d openclaw -c "
SELECT lease_id, payload->'gate_fail_reasons' AS reasons
FROM learning.lal_audit
WHERE auto_approved = false
  AND created_at > NOW() - INTERVAL '60 seconds'
ORDER BY id DESC LIMIT 20;"
# expected: 大量 row reasons 含 'health_degraded'
```

```bash
# Verify 3 — Stage 4 既有策略不受影響（Stage 4 continues per §2 M3）
curl -sS http://localhost:8001/api/v1/strategies/stage4/status | jq '.[].active'
# expected: 全 true（Stage 4 不被 DEGRADED halt，只有 Tier 1 reparam halt）
```

如任一驗收 fail → SEV-1；走 §9 escalation；M3 與 LAL 整合 regression（per ADR-0034 ↔ V106 cross-ADR collision audit Sprint 1A-ε 應 catch）。

---

## 8. Amplification Loop Cap 觸發處置

**為什麼需要 cap**（per dispatch consolidation MEDIUM E3）：M8 anomaly → M3 HEALTH_WARN → M11 divergence detector 升 warn → M8 再 detect → M3 升 DEGRADED → ... 形成 single anomaly = ∞ state change loop。

**Cap 規則**：
- Per single root anomaly_id：24h 內最多 1 次 M3 state up-transition（per dispatch consolidation MEDIUM）
- 觸發 cap 時 V106 row `amplification_cap_applied=true` + Slack alert
- Cap 觸發 = 不 promotion；on-call PM 必手動 review root anomaly

```bash
# Triage step 1 — 找 24h 內被 cap 抑制的 transition
psql -h trade-core -U openclaw -d openclaw -c "
SELECT created_at, from_state, to_state, trigger_reason, amplification_cap_applied
FROM learning.health_state_transitions
WHERE amplification_cap_applied = true
  AND created_at > NOW() - INTERVAL '24 hours';"
```

```bash
# Triage step 2 — 對應 anomaly_id 是否真實
psql -h trade-core -U openclaw -d openclaw -c "
SELECT anomaly_id, severity, payload->>'root_cause' AS rc
FROM learning.anomaly_events
WHERE anomaly_id = '<from cap log>';"
```

如 root anomaly 真實但 cap 抑制 → on-call PM **手動** trigger state change（per §5 emergency unlatch）+ 補 24h postmortem 解釋為何單一 anomaly 反復觸發；如 root anomaly 是 false positive → M8 / M11 source 調整不在本 runbook scope。

---

## 9. Escalation

**Trigger**：§4 任一 Step 顯示 SEV-1；§5 mitigation 失敗；§7 LAL 降階驗收 fail；§8 cap 反復觸發 ≥ 3 day。

**Escalation channel**：
- SEV-1：Slack `#ops-critical` + 電話 PM + email Operator
- SEV-2：Slack `#ops-warn` + email PM
- SEV-3：Slack `#ops-info`

**Attach evidence**：
- `learning.health_state_transitions` 24h 全 export
- `learning.health_observations` 觸發 transition 的 domain × score
- `learning.lal_audit` 60s 內 row（驗 §7）
- `learning.anomaly_events` 對應 root anomaly_id
- engine.log 最近 1h `m3_*` grep
- 6 baseline healthcheck 同期 status

**Post-escalation action**：
- PM 30 min 內派 E2 review 對抗性核 M3 ↔ LAL 5-gate inheritance
- 24h 內補 postmortem `docs/audits/<date>--m3_<incident>_postmortem.md`

---

## 10. Post-Incident

### Postmortem template

```markdown
# M3 Health Incident Postmortem — <YYYY-MM-DD>

## TL;DR
- State trajectory: NORMAL → ? → ? → ...
- Trigger domain(s): <ws_latency | rest_success | db_backlog | disk | engine | strategy>
- Affected strategy(ies) / LAL gate halt count: <list>
- Operator action(s) taken: <list>
- Recovery time to NORMAL: <duration>

## Timeline (UTC)
- T+0: <state up-transition>
- T+N: <step taken>

## Root cause
- 6 domain 中哪個 probe 真實出問題？
- 是 probe FP / 真 incident / amplification loop / external dependency？
- Cap 是否被觸發？是否抑制了真實 escalation？

## Mitigation
- 即時 mitigation (§5/§7/§8 對應)
- 永久 mitigation（V106 schema / M3 ADR / probe threshold 調整）

## Action items
- [ ] V106 retention / hypertable chunk 調整
- [ ] Domain N threshold 調整
- [ ] Amplification cap 規則更新
- [ ] runbook §X 更新

## 12-week trend
- 加入 monthly M3 trend dashboard tracking entry（link）
```

### 12-week trend tracking entry

每月 PM Monthly Operator Review Wizard（per CR-11 / A3 sign-off）含 M3 section：
- 4 週 / 12 週 state up-transition count by domain
- Cap 觸發次數 + cap抑制是否導致真實 incident 延遲
- LAL halt count by state（HEALTH_DEGRADED 期間 fallback_count）
- Recovery median time per state

Dashboard：`http://localhost:8001/console#health/m3` → "12w trend" tab（pending Sprint 1A-ε A3 land）。

---

## 11. Cross-References

- **v5.8 §2 M3**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:123-151`（4-state ladder + 6 domain + degradation 行為）
- **v5.8 §11.5**：同上 line 864-897（5-gate auto path inheritance；HEALTH_DEGRADED → LAL 1+2 fallback Advisory）
- **ADR-0034 LAL**：`docs/adr/0034-decision-lease-layered-approval-lal.md`（LAL gate gate_fail_reasons 含 'health_degraded'）
- **AMD-2026-05-21-01**：`docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md`（M3 Tier 1+2 opt-in scope）
- **V106 schema spec**（pending CR-8）：`docs/execution_plan/specs/2026-05-21--v106-health-observations.md`（hypertable 7d chunk + 7d compression + 90d retention）
- **既有 baseline healthcheck**：`helper_scripts/canary/engine_watchdog.py` / `helper_scripts/db/passive_wait_healthcheck.py`
- **既有 H0 runbook（風格參考）**：`docs/runbooks/2026-05-11--lg1_h0_flip_rollback.md`
- **M11 runbook（amplification loop 對應）**：`docs/runbooks/2026-05-21--m11_replay_divergence_triage_runbook.md`
- **M7 runbook（DECAY_ENFORCED 與 strategy domain 6 對應）**：`docs/runbooks/2026-05-21--m7_decay_alert_runbook.md`
- **Metric dashboard**：`http://localhost:8001/console#health/m3`（pending）
- **Healthcheck integration**：`helper_scripts/db/passive_wait_healthcheck.py --check m3_state_consistency`（pending）
- **CLAUDE.md hard boundaries**：§四 D2 portfolio cum loss > $3,000 既有 kill criteria；本 runbook 不取代

---

## 12. Version History

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| **v0.1** | 2026-05-21 | TW | Sprint 1A-β deliverable draft；4-state ladder + 6 domain triage + amplification cap + LAL 降階驗收 + 6 反向 attack mitigation 對應 M3 |

---

*OpenClaw / Arcane Equilibrium Runbook — M3 健康監控 on-call response SOP (Draft — V106 schema + M3 ADR land 後 v1 promote)*
