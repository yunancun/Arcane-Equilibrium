# M1 LAL — Tier 升降 / Auto-Approve / Manual Override SOP

**狀態：** Draft（Sprint 1A-β deliverable；CR-2 + ADR-0034 land 後 verify）
**版本：** v0.1（2026-05-21）
**Runbook ID：** RUNBOOK-M1-LAL-001
**Module：** M1 Decision Lease Layered Approval (LAL)
**Severity coverage：** SEV-1 / SEV-2 / SEV-3
**On-call role：** Operator + PM（assistive Cowork 提供 Console undo 入口，不做 approve 判斷）
**Depends on：** ADR-0034 (LAL 5-tier) / ADR-0008 (Decision Lease baseline) / AMD-2026-05-21-01 (autonomy vs human final review) / V112 schema (placeholder pending CR-8)

> **Hands off — operator only**：LAL 3 / LAL 4 永遠由 Operator 經 Console 親手 approve；本 runbook 列的 IPC patch / SQL update **僅供 emergency mitigation**，平常運維走 Console UI。

---

## 1. TL;DR / 用途

LAL（Layered Approval Lease）是 ADR-0034 為 v5.8 §2 M1 「Decision Lease 自主提案→執行迴路」設計的 5 層治理層。每筆 decision 仍 emit lease（per ADR-0008 baseline），但 emit 後分流到不同 approval 路徑：

- **LAL 0**（per-fill）— 永遠 autonomous（既有 Guardian）
- **LAL 1**（intra-strategy reparam）— Stage 4 + 30d stable 後 auto-approve（per 6 條 hard gate）
- **LAL 2**（cross-strategy reweight）— Y1 Advisory / Y2 auto with gate
- **LAL 3**（new strategy promotion）— **永遠 operator approval**
- **LAL 4**（capital structure / venue change）— **永遠 operator approval + attestation + audit + 24h clawback**

本 runbook 規範 4 類事件：(a) **Tier 升降**（per-strategy / per-LAL Console toggle 切換）/ (b) **auto-approve gate fail 處置**（fall-back 到 Advisory）/ (c) **LAL 4 manual approval flow**（含 attestation + audit）/ (d) **24h undo 觸發**（config + risk envelope only，**fills 已成交不可逆**）。

---

## 2. Detection / Alarm Symptoms

| Symptom | 來源 | 對應 section |
|---|---|---|
| Console `Auto-Approve On` toggle 切換 audit row 多了一筆 | `learning.lal_toggle_audit` | §4 Tier 升降 |
| `agent.lal_auto_approval` Slack notification 突然斷流 24h | Slack channel + `learning.lal_audit` | §5 auto-approve fail |
| Operator 發現某 LAL 1 / LAL 2 自動執行的 decision 應該 push back | Console banner + Slack notification | §7 24h undo |
| Strategist 提了 LAL 3 / LAL 4 proposal pending operator click | Console proposal queue | §6 LAL 4 manual approval |
| `lal_yes_rate` rolling 30d 跌破 80% 但 toggle 仍 ON | `learning.lal_audit` query | §5 auto-approve fail |
| 同 `(strategy, proposal_hash, lease_window_start)` 三元組 conflict（payload_hash 漂移） | engine.log + Slack alert | §8 反向 attack mitigation 第 1 條 |

---

## 3. Severity Matrix

| Severity | Impact | Response time | Escalation path |
|---|---|---|---|
| **SEV-1** | LAL gate 整體失效（任一 LAL level auto-approve 路徑寫 live state **繞過** 5-gate）；或 LAL 3 / LAL 4 被誤 auto-approve | < 5 min | Operator 立刻 `/api/v1/lal/emergency_disable_all` → 全 LAL toggle 強制 OFF；PM 30 min 內加入；24h postmortem |
| **SEV-2** | 單一 strategy LAL 1 / LAL 2 auto-approve 條件不再滿足但 toggle 仍 ON；或 V112 audit row 寫入失敗 | < 30 min | Operator 透過 Console disable 該 strategy LAL toggle；PM 4h 內加入；補 audit row |
| **SEV-3** | Console undo button 在 24h 內被點擊但 fills 已成交（預期行為，但需澄清給 operator）；或 LAL 3/4 proposal queue 累積 SLA 跨 30d | < 4h | On-call PM 回應 Slack；Console tooltip 提示「fills 不可逆」；30d SLA 升 P1 ticket |

> **判定 SEV-1 還是 SEV-2 的關鍵**：是否有 lease emit 但 `gate_pass_count < 5`（5 個 gate 任一 fail 仍寫 live state）。任一筆 = SEV-1；只是 toggle 條件 drift = SEV-2。

---

## 4. Initial Triage Checklist（5-10 步）

```bash
# Step 1 — 確認當前 LAL toggle 全景（每 strategy × 每 LAL level）
curl -sS -H "Cookie: $OPERATOR_SESSION_COOKIE" \
  http://localhost:8001/api/v1/lal/toggles | jq
# expected: per-strategy + per-LAL level boolean；default OFF；如 ON 數量 > expected → 進 §5
```

```bash
# Step 2 — 確認 V112 audit log 最後 100 筆 auto-approval
psql -h trade-core -U openclaw -d openclaw -c "
SELECT lease_id, strategy_name, lal_level, gate_pass_count, auto_approved, created_at
FROM learning.lal_audit
ORDER BY id DESC LIMIT 100;"
# decision branch:
#   - 任一 row gate_pass_count < 5 → SEV-1（立進 §9 escalation）
#   - lal_level >= 3 且 auto_approved = true → SEV-1（不應 auto；§9）
#   - rolling 30d yes-rate 統計與 toggle 不符 → SEV-2（§5）
```

```bash
# Step 3 — 確認 Decision Lease baseline 還活著（不能 LAL 失效拖累 ADR-0008）
curl -sS http://localhost:8001/api/v1/lease/health | jq '.emit_rate_5min, .sign_rate_5min'
# expected: emit_rate_5min > 0；如 0 → ADR-0008 baseline 本身炸 → 不屬本 runbook scope，轉 ADR-0008 runbook
```

```bash
# Step 4 — 確認 Guardian + 5-gate fail-closed 路徑無 regression
psql -h trade-core -U openclaw -d openclaw -c "
SELECT block_reason, COUNT(*) FROM learning.guardian_block_log
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY 1 ORDER BY 2 DESC LIMIT 10;"
# decision branch:
#   - 預期 reason 有 LAL gate fail（如 'lal_gate_fail_*'）→ fall-back Advisory 正常
#   - 0 row 但 §5 顯示 auto-approve 持續 → §11.5 5-gate 繞過嫌疑（SEV-1）
```

```bash
# Step 5 — 確認 24h undo 視窗內可 undo 的 lease 計數
psql -h trade-core -U openclaw -d openclaw -c "
SELECT COUNT(*) FROM learning.lal_audit
WHERE auto_approved = true
  AND lal_undone = false
  AND created_at > NOW() - INTERVAL '24 hours';"
# 若需要 batch undo（極端事件）→ §7
```

```bash
# Step 6 — Slack notification + Console banner 路徑健康
curl -sS http://localhost:8001/api/v1/notify/health | jq '.slack_ok, .email_ok, .console_banner_ok'
# 任一 false → SEV-2（auto-approve gate criteria #6 post-hoc transparency 失效）
# 處置：先 disable 所有 LAL 1/2 toggle 直到通知路徑復原
```

```bash
# Step 7 —（only if SEV-1）emergency disable all
curl -sS -X POST -H "Cookie: $OPERATOR_SESSION_COOKIE" \
  http://localhost:8001/api/v1/lal/emergency_disable_all
# expected: 200 OK + body 含 toggle_count_before + after = 0
# 立刻 §9 escalate；PM 30 min 內加入
```

---

## 5. Mitigation — Auto-Approve Gate Fail → Fall-back Advisory

**觸發**：6 條 hard gate 任一 fail（per ADR-0034 Decision 5 / §11.5 5-gate inheritance）。

```bash
# Mitigation step 1 — 確認 fail gate 編號 + reason
psql -h trade-core -U openclaw -d openclaw -c "
SELECT lease_id, strategy_name, lal_level, gate_pass_count,
       payload->'gate_fail_reasons' AS fail_reasons
FROM learning.lal_audit
WHERE auto_approved = false
  AND created_at > NOW() - INTERVAL '1 hour'
ORDER BY id DESC LIMIT 50;"
# fail_reasons 6 種對應 §4.5 auto-approval gate criteria：
#   '#1 prior_approval_threshold' / '#2 incident_in_90d' / '#3 risk_envelope_outside'
#   '#4 console_toggle_off' / '#5 undo_path_unavailable' / '#6 post_hoc_transparency_fail'
```

```bash
# Mitigation step 2 — fall-back Advisory（proposal queue 持續，等 operator click）
# 預期 effect：lease 仍 emit 但 status='pending_advisory'；不寫 live state；無 silent drop
# 預期 rollback：操作員修正 fail gate 條件後（如清 incident / 重置 yes-rate window），下個 proposal 自動回到 auto path
```

```bash
# Mitigation step 3 — 預期 SLA：Advisory queue 30d 內必 operator click，否則升 P1 ticket
# 預期 effect：per AMD-2026-05-21-01 §3 inactivity > 60d → 整 opt-in scope 自動回 Advisory 兼 alert PM
```

**Rollback 路徑**：如 fall-back 行為本身 regression（如 fall-back 後也不 emit lease）→ 立刻 §7 emergency disable + §9 escalate；恢復 ADR-0008 baseline lease emit 路徑。

---

## 6. Mitigation — LAL 4 Manual Approval Flow（含 attestation + audit + clawback）

**Scope**：LAL 4 = capital structure / venue change（per ADR-0034）。**永遠 operator approve**；本流程是 manual SOP，不是 auto path。

```
1. Strategist / Allocator 提出 LAL 4 proposal → emit lease (lal_level=4, status='pending_operator')
2. Console 顯示 proposal banner；Slack notification 發到 #ops-critical channel
3. Operator 開啟 Console → Proposals tab → 找到該 lease_id
4. Operator 必填 attestation form（3 條）：
   (a) 「我已閱讀完整 proposal payload + 對應 ADR cross-ref」
   (b) 「我理解此 LAL 4 變更不可由 Cowork / 任何 agent 代為 approve」
   (c) 「我接受 24h clawback 不可逆 fills」
5. 2FA confirm（TOTP 或 hardware key）
6. Console 寫入 audit row：
   INSERT INTO learning.lal_audit (lease_id, lal_level=4, actor=<operator>,
                                    attestation_jsonb, two_factor_method, ...);
7. 同步寫入 V112 `lal_pre_proposal_config_snapshot` JSON（24h clawback 用）
8. 24h clawback 視窗：operator 可在 Console 點 "Clawback last LAL 4"
   → 回滾 config + risk envelope；**fills 不可逆**（per §7）
   → audit row 標 lal_undone=true + clawback_reason
9. 24h 後 clawback 失效；如需再 rollback 走 manual amendment（非本 runbook scope）
```

**Hands off — operator only**：上 8 步全部走 Console UI；不接受任何 CLI / IPC patch 代執行。

---

## 7. 24h Undo SOP（config + risk envelope only，**fills 不可逆**）

**範圍硬邊界**（per ADR-0034 Decision 5）：

| 在 undo 範圍 | 不在 undo 範圍 |
|---|---|
| Strategy parameter snapshot（pre-proposal） | 已成交 fills（exchange 端不可逆） |
| Risk envelope snapshot（pre-proposal） | 已聚合的 PnL panel / derived data |
| Lease record 標記 `lal_undone=true` | 已寫入 audit log 的歷史 record（保留完整性） |
| Slack / email / Console 通知「undo executed」 | 已影響的下游 strategy decision（鏈式不還原） |

```bash
# Undo step 1 — 列 24h 內可 undo 的 lease
psql -h trade-core -U openclaw -d openclaw -c "
SELECT lease_id, strategy_name, lal_level, created_at,
       payload->'pre_proposal_config_snapshot' IS NOT NULL AS snapshot_present
FROM learning.lal_audit
WHERE auto_approved = true
  AND lal_undone = false
  AND created_at > NOW() - INTERVAL '24 hours';"
```

```bash
# Undo step 2 — Console 點 "Undo last auto-approval"
# 或（emergency）CLI:
curl -sS -X POST -H "Cookie: $OPERATOR_SESSION_COOKIE" \
  -d '{"lease_id":"<lease_id>"}' \
  http://localhost:8001/api/v1/lal/undo
# expected: 200 OK；audit row lal_undone=true；Slack 通知 emit；Console banner 顯示 "config + risk envelope reverted; fills NOT reversed"
```

**反模式**（明示禁止）：

- (a) 嘗試把 fills 也 undo → exchange 端不可逆；任何 client-side 假裝 rollback fills 違反 §二 原則 8「交易必可重構並解釋」
- (b) 24h 後再 undo → button disabled；如真需 rollback 走 Operator manual amendment（PM 主導）
- (c) Cowork / agent 代執行 undo → undo 是 operator-only path（per AMD-2026-05-21-01 protected scope）

---

## 8. 反向 Attack 6 條 Mitigation（per §11.5 / H-11）— M1 對應條目

### Attack 1：`(strategy, proposal_hash, lease_window_start)` payload_hash 漂移

**症狀**：同三元組重發但 `payload_hash` 不同 → engine.log 出現 `lal_payload_drift` warning。

**Mitigation**（per ADR-0034 Decision 2 conflict resolution）：
- 視為 payload 漂移 fail-closed
- Slack alert PM：「同 proposal 同窗口被改動」
- 拒絕 emit；強制 operator manual review

### Attack 2：24h undo 已 fill 不可逆

**症狀**：operator 期望 undo = 全 rollback 但 fills 已成交。

**Mitigation**（per ADR-0034 Decision 5 + §11.5）：
- Console undo button hover tooltip 明示「fills already executed cannot be undone」
- Slack notification body 含 affected fills 列表（symbol / qty / fill_price）
- §7 反模式 (a) 明示禁止假裝 rollback fills

### Attack 3：rolling 30d yes-rate 跨閾值瞬時（80% boundary flicker）

**症狀**：operator yes-rate 在 80% 上下抖動；auto-approve 路徑反覆 flip on/off。

**Mitigation**：
- §Decision 3 設計為「**嚴格大於 80%**，不含等於」
- 加 hysteresis：toggle 重新 on 需 yes-rate 連續 7d > 80%
- min N=30 prior Advisory approvals 不變

### Attack 4：Console toggle 被 session hijack 強行 ON

**症狀**：未授權 session 切 toggle。

**Mitigation**（per ADR-0034 Decision 4）：
- Toggle 切換需 Operator role + 2FA（TOTP / hardware key）
- 每次切換 `learning.lal_toggle_audit` 寫 row（actor / before / after / 2FA result）
- §4 Step 6 healthcheck 確認 toggle 路徑只接 Operator role

### Attack 5：Slack notification 斷流但 auto-approve 持續

**症狀**：post-hoc transparency gate（#6）通知路徑炸但 LAL 1/2 仍 auto。

**Mitigation**：
- 6 條 hard gate 任一 fail → fall-back Advisory（§5）
- §4 Step 6 監控 notification 路徑健康
- Notification 路徑炸 = LAL toggle 自動 OFF（Console banner 提示）

### Attack 6：操作員 inactivity > 60d 但策略繼續 auto

**症狀**：operator 60d 沒回 Console；LAL 1/2 持續 auto-approve。

**Mitigation**（per AMD-2026-05-21-01 §3）：
- 60d inactivity → opt-in scope 自動回 Advisory
- 90d inactivity → 全 LAL 1/2 toggle 強制 OFF + Slack 升 PM
- 120d → 全策略 paused（fail-safe to Stage 0R replay-only）

---

## 9. Escalation

**Trigger**：§4 任一 Step 顯示 SEV-1；或 §5 mitigation 失敗；或 §6 LAL 4 manual approval 流程被嘗試繞過。

**Escalation channel**：
- SEV-1：Slack `#ops-critical` + 電話 PM + email Operator
- SEV-2：Slack `#ops-warn` + email PM
- SEV-3：Slack `#ops-info`

**Attach evidence**：
- `learning.lal_audit` 最新 100 row 全 export（含 gate_pass_count / fail_reasons）
- engine.log 最近 1h `lal_*` grep
- Console screenshot（toggle 全景 + proposal queue）
- `learning.guardian_block_log` 24h block reason 分布
- `learning.lal_toggle_audit` 24h 切換 history

**Post-escalation action**：
- PM 30 min 內派 sub-agent E2 review 對抗性核 LAL gate inheritance
- 24h 內補 postmortem `docs/audits/<date>--lal_<incident>_postmortem.md`

---

## 10. Post-Incident

### Postmortem template

```markdown
# LAL Incident Postmortem — <YYYY-MM-DD>

## TL;DR
- Severity: SEV-?
- Affected LAL level(s): LAL ?
- Affected strategy(ies): <list>
- Lease IDs involved: <list or query>
- Operator action(s) taken: <list>

## Timeline (UTC)
- T+0: <symptom detected>
- T+N: <step taken>

## Root cause
- Which of 6 hard gate failed / which §8 attack vector triggered?
- Is V112 schema constraint sufficient?
- Did ADR-0034 Decision 1-5 cover this case?

## Mitigation
- 即時 mitigation (§5/§6/§7 對應)
- 永久 mitigation（schema / ADR / runbook 更新）

## Action items
- [ ] V112 schema 補 column / constraint
- [ ] ADR-0034 amendment 對應 attack vector
- [ ] runbook §X 更新

## 12-week trend
- 加入 monthly LAL trend dashboard tracking entry（link）
```

### 12-week trend tracking entry

每月 PM Monthly Operator Review Wizard（per CR-11 / A3 sign-off）含 LAL section：
- 4 週 / 12 週 auto-approve count by strategy × LAL level
- 6 hard gate fail rate by gate #
- 24h undo trigger count + fills not reversed reason
- LAL 4 manual approval median latency

Dashboard：`http://localhost:8001/console#governance/lal` → "12w trend" tab（pending Sprint 1A-ε A3 land）。

---

## 11. Cross-References

- **ADR-0034**：`docs/adr/0034-decision-lease-layered-approval-lal.md`（LAL 5-tier baseline + 5 Decision + LAL ↔ Stage 對齊矩陣 + 6 hard gate）
- **ADR-0008**：`docs/adr/0008-decision-lease-state-machine.md`（Decision Lease emit / sign / settle / replay baseline，本 runbook 不繞過）
- **AMD-2026-05-21-01**：`docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md`（autonomy directive；protected scope vs opt-in scope；60d/90d/120d inactivity ladder）
- **AMD-2026-05-09-03**：`docs/governance_dev/amendments/2026-05-09--strategist_wide_adjustment_skill.md`（RuntimeMaxEnvelope 是 §Decision 5 gate #3 risk envelope check）
- **v5.8 §2 M1**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:59-87`（module 來源）
- **v5.8 §11 + §11.5**：同上 line 847-897（operator forgetfulness 6 條 mitigation + 5-gate auto path inheritance）
- **V112 schema spec**（pending CR-8）：`docs/execution_plan/specs/2026-05-21--v112-decision-lease-lal.md`
- **Metric dashboard**：`http://localhost:8001/console#governance/lal`（pending Sprint 1A-ε）
- **Healthcheck script**：`helper_scripts/db/passive_wait_healthcheck.py --check lal_audit_chain`（pending）
- **Sibling runbook 風格參考**：`docs/runbooks/2026-05-11--lg1_h0_flip_rollback.md` + `docs/runbooks/replay_signing_key_rotation.md`
- **CLAUDE.md hard boundaries**：§四「ML / DreamEngine / ExecutorAgent / StrategistAgent 不可繞 GovernanceHub + Decision Lease」

---

## 12. Version History

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| **v0.1** | 2026-05-21 | TW | Sprint 1A-β deliverable draft；ADR-0034 5 Decision + LAL ↔ Stage 對齊矩陣 + 6 hard gate + 24h undo fills 不可逆 + 6 反向 attack mitigation |

---

*OpenClaw / Arcane Equilibrium Runbook — M1 LAL Tier 升降 / Auto-Approve / Manual Override SOP (Draft — V112 schema + ADR-0034 land 後 v1 promote)*
