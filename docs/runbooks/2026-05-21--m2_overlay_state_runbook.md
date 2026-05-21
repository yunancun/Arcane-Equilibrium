# M2 Overlay State — 介入 / Cascade / 24h Freeze / Revert SOP

**狀態：** Draft（Sprint 1A-β deliverable；CR-3 + M2 overlay spec + M11 divergence flag land 後 verify）
**版本：** v0.1（2026-05-21）
**Runbook ID：** RUNBOOK-M2-OVERLAY-001
**Module：** M2 External Overlay State（macro / on-chain / regime）
**Severity coverage：** SEV-1 / SEV-2 / SEV-3
**On-call role：** Operator + PM（Strategist / DreamEngine 提供 advisory，不直接 mutate overlay state）
**Depends on：** M2 overlay spec（pending CR-3）/ M3 strategy gating / M11 divergence flag / H-11 #2 false anomaly cascade mitigation / ADR-0008 Decision Lease baseline

> **Hands off — operator only**：overlay state revert 與 24h freeze 永遠由 Operator 經 Console 親手執行；本 runbook 列的 IPC patch / SQL update **僅供 emergency mitigation**，平常運維走 Console UI。

---

## 1. TL;DR / 用途

M2 overlay state 為 v5.8 §2 設計的「外部世界訊號 → 策略 gating」中介層。Overlay 不直接下單，但會：

- **影響 M3 strategy gating**（如 macro stress overlay = ON → 部分策略 size cap 0.5x）
- **影響 M11 portfolio weight**（如 on-chain whale outflow overlay = ON → BTC cluster weight -20%）
- **影響 Stage 0R / 1 / 2 / 3 / 4 promotion gate**（如 regime overlay = `crisis_mode` → promotion freeze）

Overlay 分 3 種類別，響應時效與 mitigation path 不同：

| 類別 | 範例 signal | 更新頻率 | Mitigation 響應時效 |
|---|---|---|---|
| **macro overlay** | CPI / FOMC / VIX | 日 / 事件 | < 4h |
| **on-chain overlay** | exchange netflow / whale txn / funding rate skew | 小時 / 即時 | < 30 min |
| **regime overlay** | trend / range / crisis / euphoria classifier | 4h-12h | < 1h |

本 runbook 規範 5 類事件：(a) **5 個 overlay state transition 需 operator 介入**（false anomaly 嫌疑 / signal source flicker / cascade 鏈確認 / 跨類別 conflict / classifier confidence < threshold）/ (b) **M2 → M3 / M11 cascade chain triage**（哪個 overlay 推哪個策略 / 跑哪個 portfolio rebalance）/ (c) **false anomaly cascade mitigation**（H-11 #2 attack pattern：偽 signal → overlay flip → strategy / portfolio 連鎖反應）/ (d) **overlay state revert + 24h freeze SOP**（操作 + 影響範圍 + 解凍條件）/ (e) **3 種類別響應差異**（macro 慢但廣 / on-chain 快但窄 / regime 介於中間）。

---

## 2. Detection / Alarm Symptoms

| Symptom | 來源 | 對應 section |
|---|---|---|
| Console overlay banner 顯示 state 變化（如 macro: normal → stress） | `learning.overlay_state` + Console banner | §4 Triage / §6 Cascade |
| 5 個 overlay state transition 之一 trigger（見 §5 表） | `learning.overlay_state` + Slack `#ops-overlay` | §5 Mitigation |
| M11 divergence flag fire（M2 overlay 與 actual M11 rebalance signal 不一致 > 閾值） | `learning.m11_divergence_log` | §6.3 cascade chain mid-stage halt |
| Operator 發現某 overlay 數據源（external API）回 stale data | external API monitor + Slack | §7 24h freeze |
| 同一 trade window 內多 overlay 同時 flip（跨類別 conflict） | `learning.overlay_state` GROUP BY window | §5 #4 mitigation |
| Regime classifier confidence < 0.6（low confidence regime call） | `learning.regime_classifier_log` | §5 #5 mitigation |

---

## 3. Severity Matrix

| Severity | Impact | Response time | Escalation path |
|---|---|---|---|
| **SEV-1** | Overlay state flip 觸發 M3 strategy gating 連帶 portfolio 全策略 size cap（如 macro: stress → 所有策略 0.5x），但發現 overlay 是 false anomaly（signal source 錯 / API stale） | < 30 min | Operator 立刻 §7 24h freeze + 全 overlay state 強制 revert；PM 1h 內加入；24h postmortem |
| **SEV-2** | 單一 overlay 類別 transition 但 cascade 影響 < 50% portfolio 或 < 3 策略；或 M11 divergence flag fire 但 portfolio weight 尚未實際 rebalance | < 1h | Operator 透過 Console review overlay → 決定 revert 或 hold；PM 4h 內加入 |
| **SEV-3** | overlay state 在閾值附近抖動（hysteresis 範圍內 flip），無實際 cascade；或 regime classifier confidence 短暫 < 0.6 | < 4h | On-call PM 回應 Slack；確認 hysteresis logic 有作用，無需 revert |

> **判定 SEV-1 還是 SEV-2 的關鍵**：cascade 是否已實際影響 portfolio weight / strategy size。任一筆 portfolio rebalance 寫入 OR 任一策略 size cap 已套用 = SEV-1；只是 overlay state 變化但 cascade 尚在 grace window = SEV-2。

---

## 4. Initial Triage Checklist（5-10 步）

```bash
# Step 1 — 確認當前所有 overlay state 全景
psql -h trade-core -U openclaw -d openclaw -c "
SELECT overlay_category, overlay_name, current_state, last_transition_at,
       payload->'signal_source' AS signal_source,
       payload->'confidence' AS confidence
FROM learning.overlay_state
WHERE active = true
ORDER BY overlay_category, last_transition_at DESC;"
# expected: 3 種類別各自 N 個 overlay；confidence > 0.6（regime）；
# decision branch:
#   - 任一 overlay 在 grace window 內（< 30 min from transition）→ §6 cascade chain triage
#   - confidence < 0.6 持續 > 1h → §5 #5 mitigation
```

```bash
# Step 2 — 確認最近 24h overlay transition history（找 false anomaly 嫌疑）
psql -h trade-core -U openclaw -d openclaw -c "
SELECT overlay_name, from_state, to_state, transitioned_at,
       payload->'trigger_signal_value' AS signal_value,
       payload->'auto_or_manual' AS trigger_type
FROM learning.overlay_transition_log
WHERE transitioned_at > NOW() - INTERVAL '24 hours'
ORDER BY transitioned_at DESC;"
# decision branch:
#   - 同一 overlay 24h 內 flip > 3 次 → false anomaly 嫌疑（§5 #1）
#   - signal_value 與外部源不一致 → API stale 嫌疑（§5 #2）
```

```bash
# Step 3 — 確認 M3 strategy gating 是否已實際套用
psql -h trade-core -U openclaw -d openclaw -c "
SELECT strategy_name, current_size_multiplier, last_overlay_applied,
       last_overlay_applied_at
FROM strategies.runtime_state
WHERE last_overlay_applied IS NOT NULL
  AND last_overlay_applied_at > NOW() - INTERVAL '1 hour';"
# decision branch:
#   - current_size_multiplier < 1.0 → cascade 已實際生效 → SEV-1
#   - last_overlay_applied 與 §1 active overlay 對應 → 預期；否則 §6.3 chain halt
```

```bash
# Step 4 — 確認 M11 portfolio weight 是否已 rebalance（cascade 第二層）
psql -h trade-core -U openclaw -d openclaw -c "
SELECT cluster_name, current_weight, target_weight, last_rebalance_at,
       payload->'trigger_overlay' AS trigger_overlay
FROM portfolio.cluster_weights
WHERE last_rebalance_at > NOW() - INTERVAL '1 hour';"
# decision branch:
#   - 任一 cluster weight 與 target diff > 5% → rebalance pending → §6.3 grace
#   - trigger_overlay 不為 NULL → cascade 已寫入 → SEV-1 if false anomaly
```

```bash
# Step 5 — 確認 M11 divergence flag 是否 fire（M2 ↔ M11 不一致 detector）
psql -h trade-core -U openclaw -d openclaw -c "
SELECT divergence_type, m2_signal, m11_actual_signal, divergence_score,
       fired_at
FROM learning.m11_divergence_log
WHERE fired_at > NOW() - INTERVAL '4 hours'
ORDER BY fired_at DESC LIMIT 20;"
# decision branch:
#   - divergence_score > 0.4 → §6.3 cascade chain mid-stage halt
#   - 0 row → cascade 路徑健康
```

```bash
# Step 6 — 確認 external signal source API 健康
curl -sS http://localhost:8001/api/v1/overlay/source_health | jq '.macro_ok, .onchain_ok, .regime_classifier_ok'
# decision branch:
#   - 任一 false → §5 #2 mitigation（API stale → overlay 應 freeze）
#   - regime_classifier_ok = false 但 macro/onchain ok → §5 #5（classifier 單獨炸）
```

```bash
# Step 7 — Slack notification + Console banner 路徑健康
curl -sS http://localhost:8001/api/v1/notify/health | jq '.slack_ok, .console_banner_ok'
# 任一 false → SEV-2（overlay state 變化但 operator 不會收到通知）
# 處置：先 §7 24h freeze 所有 overlay 直到通知路徑復原
```

```bash
# Step 8 —（only if SEV-1 + false anomaly 確認）emergency freeze
curl -sS -X POST -H "Cookie: $OPERATOR_SESSION_COOKIE" \
  http://localhost:8001/api/v1/overlay/emergency_freeze_all
# expected: 200 OK + body 含 freeze_count + freeze_until_ts (24h 後)
# 立刻 §9 escalate；PM 1h 內加入
```

---

## 5. Mitigation — 5 個 Overlay State Transition Operator 介入觸發

### #1 False anomaly 嫌疑（同 overlay 24h 內 flip > 3 次）

**症狀**：`learning.overlay_transition_log` 顯示同一 overlay_name 在 24h 內 from/to 反覆 flip > 3 次。常見於 macro CPI 數據 revision、on-chain 短期 noise spike。

**Mitigation**：
- Console 開 overlay 詳情 → 確認 hysteresis threshold 是否設過窄
- 暫時 §7 24h freeze 該 overlay → 等待 signal source 穩定
- 如 hysteresis threshold 確認過窄 → 寫 follow-up ticket 調 spec（per CR-3 overlay spec）；本 runbook 不直接改 threshold

### #2 Signal source flicker（external API stale 嫌疑）

**症狀**：`/api/v1/overlay/source_health` 任一回 false；或 `payload->'trigger_signal_value'` 與外部源公開值不一致。

**Mitigation**：
- §7 24h freeze 該 overlay（不影響其他類別）
- 確認 external API 健康後 unfreeze（健康 = 連續 1h ok）
- 如 API 持續炸 > 4h → escalate signal source 切換（manual amendment，非本 runbook scope）

### #3 Cascade 鏈確認（M2 → M3 → M11 第一層 transition 後）

**症狀**：overlay state transition 後 M3 strategy gating 已套用，但 M11 portfolio rebalance 尚在 grace window 內未執行。

**Mitigation**：
- §4 Step 3 + Step 4 確認 cascade 第一層（M3）已生效、第二層（M11）grace 中
- 如 confidence 高（regime > 0.6, on-chain signal_value 確定）→ 等 grace 自動 propagate，無需介入
- 如 §6.3 M11 divergence flag fire → halt cascade 第二層 + escalate

### #4 跨類別 conflict（同 trade window 內多 overlay 同時 flip）

**症狀**：`learning.overlay_state` GROUP BY transition_window 顯示同一 5-min window 內 macro + on-chain + regime 同時 flip。

**Mitigation**：
- Console 開 cross-category review → 確認三個 signal source 是否獨立 trigger（互不為因）
- 如獨立 → cascade 影響疊加（M3 + M11 同時 react），預期行為，但 escalate PM 確認
- 如非獨立（共同上游 signal 失效）→ §7 24h freeze 全 overlay + escalate

### #5 Regime classifier confidence < 0.6

**症狀**：`learning.regime_classifier_log` 顯示 confidence < 0.6 持續 > 1h；regime overlay 不應在 low confidence 下 trigger cascade。

**Mitigation**：
- Regime overlay 自動 fall-back 到 last_high_confidence_state（confidence 上次 > 0.7 的 state）
- Console banner 顯示 "regime classifier degraded; using last stable state"
- 如 confidence 持續 < 0.6 > 4h → §7 24h freeze regime overlay only（macro / on-chain 不影響）

---

## 6. M2 ↔ M3 / M11 Cascade Chain Triage

### 6.1 Cascade chain 全景

```
External signal source
        ↓
M2 overlay state transition（per category）
        ↓ (cascade level 1, grace window 5-15 min)
M3 strategy gating（per-strategy size_multiplier / disable）
        ↓ (cascade level 2, grace window 30-60 min)
M11 portfolio rebalance（cluster weight 調整）
        ↓ (cascade level 3, 等下個 portfolio review cycle)
Stage 0R/1/2/3/4 promotion gate（freeze / unfreeze）
```

### 6.2 哪個 overlay 推哪個策略 / portfolio

| Overlay 類別 | 推 M3 strategy | 推 M11 portfolio | 推 Stage promotion |
|---|---|---|---|
| macro: stress | 所有策略 size 0.5x | risk-off cluster +10% | promotion freeze |
| on-chain: whale outflow | BTC / ETH 策略 size 0.7x | BTC cluster -20% | BTC strategy promotion freeze |
| regime: crisis | trend-following 策略 disable | trend-cluster -50% | 全 stage promotion freeze |
| regime: euphoria | mean-reversion 策略 size 0.7x | mean-rev cluster -10% | mean-rev strategy promotion freeze |

### 6.3 Mid-stage halt（M11 divergence flag fire）

**症狀**：M2 overlay 推 M11 rebalance 但 M11 自身 signal（portfolio momentum / cluster correlation）與 M2 推測方向相反，`learning.m11_divergence_log` divergence_score > 0.4。

**Mitigation**：
- Halt M11 cascade（cluster weight 不更新）
- 保留 M3 strategy gating（已生效部分不 revert）
- Slack alert PM：「M2 ↔ M11 divergence; portfolio rebalance halted; await operator review」
- Operator review 後決定：(a) trust M2 → 強制 M11 rebalance / (b) trust M11 → revert M2 overlay state / (c) hold 直到 divergence_score < 0.2

---

## 7. False Anomaly Cascade Mitigation（H-11 #2）

**Scope**：H-11 #2 為 v5.8 §11.5 攻擊面盤點之一 —「外部偽 signal 推 M2 → M3 → M11 連鎖反應 → portfolio 大幅 rebalance → 真 signal 來時已耗 capital budget」。

### 7.1 Detection

- §4 Step 2 顯示同 overlay 24h flip > 3 次
- §4 Step 6 顯示 signal source API health 偶 flicker（intermittent，非持續 false）
- M11 divergence flag fire（M2 推 cascade 但 M11 momentum 對立）

### 7.2 Mitigation 三層防禦

**Layer 1 — Hysteresis**（spec layer，本 runbook 不改）：
- overlay state transition 需 signal 持續 > threshold 至少 N min（per CR-3 overlay spec）
- 避免 noise spike 觸發 flip

**Layer 2 — Cascade grace window**：
- M3 gating 套用前 5-15 min grace（per category）
- M11 rebalance 套用前 30-60 min grace
- Grace 期間如 overlay revert → cascade 自動取消

**Layer 3 — Operator manual freeze**：
- §4 Step 8 emergency freeze
- §8 revert SOP + 24h freeze（不 unfreeze 直到 signal source 連續 1h ok + operator review）

### 7.3 Postmortem 必填項

- 偽 signal source 是哪個（external API / classifier / 數據源）
- Hysteresis threshold 是否需要調（write follow-up ticket）
- Cascade 第幾層被 halt（M3 only / M3 + M11 / 全 cascade 走完）
- Capital budget 實際消耗 vs 預期（被偽 signal 推走的 rebalance cost）

---

## 8. Overlay State Revert + 24h Freeze SOP

### 8.1 Revert 範圍硬邊界

| 在 revert 範圍 | 不在 revert 範圍 |
|---|---|
| overlay state 本身（current_state ← previous_state） | 已執行的 fills（exchange 端不可逆） |
| M3 strategy size_multiplier（cascade level 1 已套用部分） | 已寫入 audit log 的歷史 record |
| M11 cluster_weights target_weight（cascade level 2 已 propagate 部分） | 已影響的下游 strategy decision（鏈式不還原） |
| 對應 transition_log 標記 `reverted=true` | 已聚合的 PnL / panel / derived data |

### 8.2 Revert SOP（Console UI 走法）

```
1. Operator 開 Console → Overlay tab → 找到 target overlay
2. 點 "Revert to previous state"
3. 填 revert reason（必填，自由文本 + reason category）
4. 2FA confirm（TOTP 或 hardware key）
5. Console 寫入 audit row：
   INSERT INTO learning.overlay_transition_log (overlay_name, from_state, to_state,
                                                  trigger_type='manual_revert',
                                                  reverted=true, actor=<operator>, ...);
6. 同步觸發：
   - M3 strategy size_multiplier reset 到 previous overlay snapshot
   - M11 cluster_weights target reset（grace window 內 cancel pending rebalance）
   - Slack `#ops-overlay` notification「overlay reverted; cascade rolled back to level X」
```

### 8.3 24h Freeze SOP

```
1. Operator 開 Console → Overlay tab → 點 "Freeze overlay for 24h"
2. 選 freeze scope：single overlay / single category / all overlays
3. 填 freeze reason
4. 2FA confirm
5. Console 寫入：
   UPDATE learning.overlay_state SET frozen=true, freeze_until=NOW()+INTERVAL '24 hours'
   WHERE overlay_name IN (...);
6. Frozen overlay 在 24h 內：
   - 不接受 external signal trigger
   - 不參與 M3 / M11 cascade
   - 維持 freeze 當下 state
7. 24h 後自動 unfreeze；如需提前 unfreeze 走 Console manual unfreeze + 2FA
```

### 8.4 反模式（明示禁止）

- (a) 嘗試把已執行 fills 也 revert → exchange 端不可逆；違反 §二 原則 8
- (b) 跳過 2FA 直接走 SQL update → 違反 audit chain；任何 manual SQL 必補 audit row
- (c) Strategist / Cowork 代執行 revert / freeze → overlay state mutation 是 operator-only path

---

## 9. Escalation

**Trigger**：§4 任一 Step 顯示 SEV-1；或 §5 任一 mitigation 失敗；或 §7 false anomaly cascade 已實際影響 portfolio。

**Escalation channel**：
- SEV-1：Slack `#ops-critical` + 電話 PM + email Operator
- SEV-2：Slack `#ops-overlay` + email PM
- SEV-3：Slack `#ops-info`

**Attach evidence**：
- `learning.overlay_state` 當前全景
- `learning.overlay_transition_log` 24h 內完整 history
- `learning.m11_divergence_log` 4h 內 fire 記錄
- `strategies.runtime_state` 被 cascade 影響的策略列表
- `portfolio.cluster_weights` 被 cascade 影響的 cluster
- external API health 30 min 內 sample
- Console screenshot（overlay banner + cascade chain 視圖）

**Post-escalation action**：
- PM 1h 內派 sub-agent E2 review 對抗性核 cascade chain logic
- 24h 內補 postmortem `docs/audits/<date>--overlay_<incident>_postmortem.md`

---

## 10. Post-Incident

### Postmortem template

```markdown
# Overlay Incident Postmortem — <YYYY-MM-DD>

## TL;DR
- Severity: SEV-?
- Affected overlay category: macro / on-chain / regime
- Affected overlay name(s): <list>
- Cascade level reached: 1 (M3 only) / 2 (M3 + M11) / 3 (全 cascade)
- Operator action(s) taken: <list>

## Timeline (UTC)
- T+0: <symptom detected>
- T+N: <step taken>

## Root cause
- 偽 signal 嫌疑？外部 API stale？hysteresis 設過窄？
- M11 divergence flag 是否預警但被忽略？
- Cascade grace window 是否足夠？

## Mitigation
- 即時 mitigation（§5/§7/§8 對應）
- 永久 mitigation（spec / hysteresis threshold / cascade grace 更新）

## Action items
- [ ] CR-3 overlay spec 補 column / constraint
- [ ] cascade grace window 調整
- [ ] external signal source 切換 / 加 backup
- [ ] runbook §X 更新
```

### 12-week trend tracking entry

PM Monthly Operator Review Wizard 含 overlay section：
- 4 週 / 12 週 overlay transition count by category × overlay_name
- false anomaly 確認次數 + 對應 trigger pattern
- M11 divergence flag fire count + outcome（trust M2 / trust M11 / hold）
- 24h freeze trigger count + freeze reason 分布

Dashboard：`http://localhost:8001/console#governance/overlay` → "12w trend" tab（pending Sprint 1A-ε A3 land）。

---

## 11. Cross-References

- **CR-3 overlay spec**（pending）：`docs/execution_plan/specs/2026-05-21--m2-overlay-spec.md`
- **M3 strategy gating spec**：`docs/architecture/m3_strategy_gating.md`（pending）
- **M11 portfolio rebalance spec**：`docs/architecture/m11_portfolio_rebalance.md`（pending）
- **M11 divergence flag**：`docs/execution_plan/specs/2026-05-21--m11-divergence-flag.md`（pending CR-X）
- **ADR-0008**：`docs/adr/0008-decision-lease-state-machine.md`（cascade 影響的 strategy 仍需 Decision Lease 走 emit/sign/settle）
- **v5.8 §2 M2**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md`（module 來源）
- **v5.8 §11.5 H-11 #2**：同上（false anomaly cascade attack pattern 來源）
- **Metric dashboard**：`http://localhost:8001/console#governance/overlay`（pending Sprint 1A-ε）
- **Healthcheck script**：`helper_scripts/db/passive_wait_healthcheck.py --check overlay_cascade_chain`（pending）
- **Sibling runbook**：`docs/runbooks/2026-05-21--m1_lal_operator_runbook.md`（LAL 5-tier; 6 hard gate; 24h undo）/ `docs/runbooks/2026-05-11--lg1_h0_flip_rollback.md`
- **CLAUDE.md hard boundaries**：§四「ML / DreamEngine / ExecutorAgent / StrategistAgent 不可繞 GovernanceHub + Decision Lease」（overlay mutation 屬同 boundary）

---

## 12. Version History

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| **v0.1** | 2026-05-21 | TW | Sprint 1A-β deliverable draft；5 overlay transition operator 介入 + M2 ↔ M3 / M11 cascade 三層 + H-11 #2 false anomaly cascade 三層防禦 + revert + 24h freeze SOP + 3 種類別響應差異 |

---

*OpenClaw / Arcane Equilibrium Runbook — M2 Overlay State 介入 / Cascade / 24h Freeze / Revert SOP (Draft — CR-3 overlay spec + M11 divergence flag land 後 v1 promote)*
